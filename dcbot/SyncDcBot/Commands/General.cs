using Discord.Interactions;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Repositories;
using SyncDcBot.Services;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Commands;

public class GeneralModule(
    CommandResultStore resultStore,
    VerificationService verificationService,
    IConfiguration configuration) : CommandBase(resultStore)
{
    [SlashCommand("ping", "Check if bot is up")]
    public async Task PingAsync()
    {
        ResultStore.SetSuccess(Context.Interaction.Id, $"🏓 Pong! Delay: **{Context.Client.Latency}ms**",
            responseType: BotResponseType.Visible);
    }

    // [SlashCommand("send", "Send an email")]
    // public async Task SendEmailAsync(
    //     [Summary("email", "Email address)")] string email)
    // {
    //     var mailTo = email;
    //     var subject = "Paczka - kod weryfikacyjny";
    //     var body = "Test";
    //
    //     await Context.Interaction.DeferAsync();
    //     var result = await gmailSenderService.SendMessage(mailTo, subject, body);
    //
    //     var commandResult = ConvertGmailResultToCommandResult(result, email);
    //     ResultStore.Set(Context.Interaction.Id, commandResult);
    // }

    [SlashCommand("verify", "Send verification code")]
    public async Task VerifyAsync(
        [Summary("email", "Email address)")] string email)
    {
        var codeExpiryTime = TimeSpan.FromMinutes(
            configuration.GetValue<int>("DiscordConfig:VerificationCodeExpiryMinutes", 15));
        var emailDomain = configuration.GetValue<string>("DiscordConfig:StudentEmailDomain")!;
        var userDiscordId = Context.User.Id;

        await Context.Interaction.DeferAsync();
        var result = await verificationService.StartVerification(userDiscordId, email);

        var pendingData = (result as ServiceResult<SendCodeResultType, SendCodePendingData>)?.Data;
        var emailFailData = (result as ServiceResult<SendCodeResultType, EmailFailedData>)?.Data;

        var commandResult = result.Type switch
        {
            SendCodeResultType.Success             => CommandResult.Success(
                $"Verification email sent to {email}",
                $"Verification code sent to `{email}`. Code is valid for {codeExpiryTime.TotalMinutes} minutes."),
            SendCodeResultType.CodeAlreadyPending  => CommandResult.Failure(
                $"Code has already been sent to {email} at {pendingData!.Entry.SentAt}.",
                $"Code has been already sent. Check your inbox/junk folder. If you can't find it, wait until {pendingData!.Entry.ExpiresAt} and try again"),
            SendCodeResultType.InvalidEmailFormat  => CommandResult.Failure(
                $"Invalid email format for userId={userDiscordId}: {email}",
                $"Email must be in format `s123456{emailDomain}`"),
            SendCodeResultType.EmailDeliveryFailed => ConvertGmailResultToCommandResult(emailFailData!.Data,email),
            _ => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }

    private CommandResult ConvertGmailResultToCommandResult(ServiceResult<GmailResultType> result, string email)
    {
        var commandResult = result.Type switch
        {
            GmailResultType.Success             => CommandResult.Success(
                $"Verification code sent to `{email}`. Check junk/spam folder if you can't find it"),
            GmailResultType.RecipientNotFound   => CommandResult.Failure(result.Message, "Invalid email address."),
            GmailResultType.RateLimitExceeded   => CommandResult.GeneralError(logMsg: result.Message!),
            GmailResultType.Unauthorized        => CommandResult.GeneralError(logMsg: result.Message!),
            GmailResultType.UnexpectedError     => CommandResult.GeneralError(logMsg: result.Message!),
            _ => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        return commandResult;
    }
}