using System.Reflection;
using Discord;
using Discord.Commands;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Serilog;
using SyncDcBot.Repositories;
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
    
    private const string LogTemplate = "/{Command} [{Parameters}] by {User}({UserId})";
    private const string LogTemplateWithMessage = LogTemplate + " -> {Message}";
    private const string LogTemplateErrorWithMessage = LogTemplate + " failed -> {Reason}";
    
    
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
        var guildId = ulong.Parse(_config["GuildId"]!);
        
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

        if (!result.IsSuccess)
        {
            await HandleError(cmd, ctx, result, parameters);
            return;
        }
        
        HandleSuccess(cmd, ctx, businessResult, parameters);
    }

    private static string ExtractCommandParameters(IInteractionContext ctx)
    {
        return ctx.Interaction is SocketSlashCommand slashCmd
            ? string.Join(", ", slashCmd.Data.Options.Select(o => $"{o.Name}: {o.Value}"))
            : "";
    }

    private void HandleSuccess(SlashCommandInfo cmd, IInteractionContext ctx, CommandResult? businessResult, string parameters)
    {
        if (businessResult is not null)
        {
            _logger.Write(businessResult.LogLevel, LogTemplateWithMessage,
                cmd.Name, parameters, ctx.User.Username, ctx.User.Id, businessResult.Message);
        }
        else
        {
            _logger.Information(LogTemplate,
            cmd.Name, parameters, ctx.User.Username, ctx.User.Id);
        }
    }

    private async Task HandleError(SlashCommandInfo cmd, IInteractionContext ctx, IResult result, string parameters)
    {
        _logger.Warning(LogTemplateErrorWithMessage,
            cmd.Name, parameters, ctx.User.Username, ctx.User.Id, result.ErrorReason);

        var msg = result.Error switch
        {
            InteractionCommandError.UnmetPrecondition => $"{EmojiRepo.ErrorEmoji} No permission to execute this command: {result.ErrorReason}",
            InteractionCommandError.Exception         => $"{EmojiRepo.ErrorEmoji} Error: {result.ErrorReason}",
            _                                         => $"{EmojiRepo.ErrorEmoji} {result.ErrorReason}"
        };

        if (ctx.Interaction.HasResponded)
        {
            await ctx.Interaction.FollowupAsync(msg, ephemeral: true);
        }
        else
        {
            await ctx.Interaction.RespondAsync(msg, ephemeral: true);
        }
    }
}