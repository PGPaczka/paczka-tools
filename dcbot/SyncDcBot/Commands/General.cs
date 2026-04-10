using Discord.Interactions;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Repositories;
using SyncDcBot.Services;
using SyncDcBot.Types;

namespace SyncDcBot.Commands;

public class GeneralModule(CommandResultStore resultStore, GmailSenderService gmailSenderService, IConfiguration configuration) : CommandBase(resultStore)
{
    [SlashCommand("ping", "Check if bot is up")]
    public async Task PingAsync()
    {
        ResultStore.SetSuccess(Context.Interaction.Id, $"🏓 Pong! Delay: **{Context.Client.Latency}ms**", responseType: BotResponseType.Visible);
    }
    
    [SlashCommand("verify", "Send verification code")]
    public async Task VerifyAsync(
        [Summary("email", "Email address that the verification code will be sent to)")]
        string email)
    {
        var mailTo = email;
        var subject = "Paczka - kod weryfikacyjny";
        var body = "Test";
        
        await Context.Interaction.DeferAsync();
        var result = await gmailSenderService.SendMessage(mailTo, subject, body);

        var errorMsg = $"Something went wrong. Contact the admin (<@&{configuration["DiscordConfig:AdminRoleId"]}>) for help.";
        var commandResult = result.Type switch
        {
            GmailResultType.Success           => CommandResult.Success($"Verification code sent to `{email}`. Check junk/spam folder if you can't find it"),
            GmailResultType.RecipientNotFound => CommandResult.Failure(result.Message, "Invalid email address."),
            GmailResultType.RateLimitExceeded => CommandResult.Error(result.Message, errorMsg),
            GmailResultType.Unauthorized      => CommandResult.Error(result.Message, errorMsg),
            GmailResultType.UnexpectedError   => CommandResult.Error(result.Message, errorMsg),
            _                                 => CommandResult.Error("ERROR")
        };
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }
    
} 