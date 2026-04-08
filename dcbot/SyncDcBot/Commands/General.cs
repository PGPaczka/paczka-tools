using Discord.Interactions;
using Microsoft.Extensions.Configuration;
using Serilog.Events;
using SyncDcBot.Repositories;
using SyncDcBot.Services;

namespace SyncDcBot.Commands;

public class GeneralModule(CommandResultStore resultStore, GmailSenderService gmailSenderService, IConfiguration configuration) : CommandBase(resultStore)
{
    [SlashCommand("ping", "Check if bot is up")]
    public Task PingAsync()
    {
        ResultStore.SetSuccess(Context.Interaction.Id, $"🏓 Pong! Delay: **{Context.Client.Latency}ms**", BotResponseType.Visible);
        return Task.CompletedTask;
    }
    
    [SlashCommand("verify", "Send verification code")]
    public async Task VerifyAsync(
        [Summary("email", "Email address that the verification code will be sent to)")]
        string email)
    {
        var mailTo = email;
        var subject = "Paczka - kod weryfikacyjny";
        var body = "Test";
        var result = (await gmailSenderService.SendMessage(mailTo, subject, body)).ToCommandResult();

        if (result.IsSuccess)
        {
            ResultStore.SetSuccess(Context.Interaction.Id, $"Verification code sent to `{email}`. Check junk/spam folder if you can't find it");
        }
        else
        {
            ResultStore.SetFailure(Context.Interaction.Id, $"Something went wrong. Contact the admin (<@&{configuration["AdminRoleId"]}>) for help.");
        }
    }
    
}