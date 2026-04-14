using System.Reflection;
using Discord;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Serilog;
using Serilog.Events;
using SyncDcBot.Repositories;
using SyncDcBot.Types;
using IResult = Discord.Interactions.IResult;

namespace SyncDcBot.Services;

public class InteractionHandler
{
    private readonly DiscordSocketClient _client;
    private readonly InteractionService _interactions;
    private readonly IServiceProvider _services;
    private readonly IConfiguration _config;
    private readonly ILogger _logger;
    private readonly CommandResultStore _resultStore;
    private readonly ulong _logChannelId;

    private const string LogTemplate = "/{Command} [{Parameters}] by {User}({UserId})";
    private const string LogTemplateWithMessage = LogTemplate + ": success -> `{Message}`";
    private const string LogTemplateErrorWithMessage = LogTemplate + ": failed -> `{Reason}`";

    public InteractionHandler(
        DiscordSocketClient client,
        InteractionService interactions,
        IServiceProvider services,
        IConfiguration config, CommandResultStore resultStore)
    {
        _client = client;
        _interactions = interactions;
        _services = services;
        _config = config;
        _resultStore = resultStore;
        _logger = Log.ForContext("Source", "Command");
        _logChannelId = ulong.Parse(config["DiscordConfig:LogChannelId"]!);
    }

    public async Task InitializeAsync()
    {
        _client.Ready += OnReadyAsync;
        _client.InteractionCreated += OnInteractionAsync;
        _interactions.SlashCommandExecuted += OnSlashCommandExecuted;

        await _interactions.AddModulesAsync(Assembly.GetEntryAssembly(), _services);
    }

    private async Task OnReadyAsync()
    {
        var guildId = ulong.Parse(_config["DiscordConfig:GuildId"]!);

        // instant registration for concrete server
        await _interactions.RegisterCommandsToGuildAsync(guildId);
        Log.ForContext("Source", "App").Information("Commands registered");
    }

    private async Task OnInteractionAsync(SocketInteraction interaction)
    {
        var ctx = new SocketInteractionContext(_client, interaction);
        await _interactions.ExecuteCommandAsync(ctx, _services);
    }

    private async Task OnSlashCommandExecuted(SlashCommandInfo cmd, IInteractionContext ctx, IResult result)
    {
        var parameters = ExtractCommandParameters(ctx);
        var businessResult = _resultStore.Take(ctx.Interaction.Id);
        businessResult ??= new CommandResult(
            IsSuccess: result.IsSuccess,
            Message: string.IsNullOrEmpty(result.ErrorReason) ? "OK" : result.ErrorReason,
            LogLevel: result.IsSuccess ? LogEventLevel.Information : LogEventLevel.Warning
        );

        var (response, logTask) = businessResult.IsSuccess
            ? HandleSuccess(cmd, ctx, businessResult, parameters)
            : HandleError(cmd, ctx, parameters, businessResult, result);

        if (businessResult.ShouldBotRespond())
        {
            var responseAction = ctx.Interaction.HasResponded
                ? ctx.Interaction.FollowupAsync(response, ephemeral: businessResult.ShouldBotRespondEphemeral())
                : ctx.Interaction.RespondAsync(response, ephemeral: businessResult.ShouldBotRespondEphemeral());
            await responseAction;
        }

        await logTask;
    }


    private static string ExtractCommandParameters(IInteractionContext ctx)
    {
        return ctx.Interaction is SocketSlashCommand slashCmd
            ? string.Join(", ", slashCmd.Data.Options.Select(o => $"**{o.Name}**: {o.Value}"))
            : "";
    }

    private (string response, Task logTask) HandleSuccess(SlashCommandInfo cmd, IInteractionContext ctx, CommandResult businessResult, string parameters)
    {
        var level = businessResult.LogLevel;
        var message = businessResult.Message;

        _logger.Write(level, LogTemplateWithMessage, cmd.Name, parameters, ctx.User.Username, ctx.User.Id, message);
    
        var logTask = SendToLogChannelAsync(FormatDiscordMessage(cmd, ctx, parameters, true, message));
        var response = $"{EmojiRepo.SuccessEmoji} {businessResult.GetUserMessage()}";
    
        return (response, logTask);
    }

    private (string response, Task logTask) HandleError(SlashCommandInfo cmd, IInteractionContext ctx, string parameters, CommandResult? businessResult, IResult result)
    {
        _logger.Warning(LogTemplateErrorWithMessage, cmd.Name, parameters, ctx.User.Username, ctx.User.Id, businessResult?.Message);
    
        var logTask = SendToLogChannelAsync(FormatDiscordMessage(cmd, ctx, parameters, false, businessResult?.Message));
        var response = GenerateErrorMessageForUser(result, businessResult);
    
        return (response, logTask);
    }

    private static string GenerateErrorMessageForUser(IResult result, CommandResult? businessResult)
    {
        if (businessResult != null)
            return $"{EmojiRepo.ErrorEmoji} {businessResult.GetUserMessage()}";

        var prefix = result.Error switch
        {
            InteractionCommandError.UnmetPrecondition => "No permission to execute this command:",
            InteractionCommandError.Exception         => "Error:",
            _                                         => ""
        };

        return $"{EmojiRepo.ErrorEmoji} {prefix} {result.ErrorReason}".Trim();
    }

    private static string FormatDiscordMessage(SlashCommandInfo cmd, IInteractionContext ctx, string parameters,
        bool isSuccess, string? result = null)
    {
        var emoji = isSuccess ? EmojiRepo.SuccessEmoji : EmojiRepo.ErrorEmoji;
        var base_ = $"{emoji} `/{cmd.Name}` [{parameters}] by {ctx.User.Mention}";
        // todo: think about it -> resultPure does not contain emoji (wanted/unwanted)? (logs channel has emojis, main channel does not)
        var resultPure = result?.Replace('`', '\'');
        return result is not null ? $"{base_} → `{resultPure}`" : base_;
    }

    private async Task SendToLogChannelAsync(string message)
    {
        if (_client.GetChannel(_logChannelId) is not ITextChannel channel) return;
        await channel.SendMessageAsync(message);
    }
}