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
        // todo: check if user already has role
        
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
            GmailResultType.Success             => CommandResult.Success($"Verification code sent to `{email}`. Check junk/spam folder if you can't find it"),
            GmailResultType.RecipientNotFound   => CommandResult.Failure(result.Message, "Invalid email address."),
            GmailResultType.RateLimitExceeded   => CommandResult.GeneralError(logMsg: result.Message!),
            GmailResultType.Unauthorized        => CommandResult.GeneralError(logMsg: result.Message!),
            GmailResultType.UnexpectedError     => CommandResult.GeneralError(logMsg: result.Message!),
            _ => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        return commandResult;
    }
    
    [SlashCommand("code", "Submit your verification code")]
    public async Task VerifyCodeAsync(
        [Summary("code", "Verification code sent to your email")] string code)
    {
        var userId = Context.User.Id;
        var result = verificationService.VerifyCode(userId, code);

        var commandResult = result switch
        {
            VerifyCodeResultType.Success          => CommandResult.Success(
                $"User {Context.User.Username} ({userId}) verified successfully.",
                "Your email has been verified successfully!"),

            VerifyCodeResultType.InvalidCode      => CommandResult.Failure(
                $"Invalid code attempt for userId={userId}.",
                "Invalid code. Please try again."),

            VerifyCodeResultType.Expired          => CommandResult.Failure(
                $"Expired code for userId={userId}.",
                "Your code has expired. Use `/verify` to request a new one."),

            VerifyCodeResultType.NotFound         => CommandResult.Failure(
                $"No pending verification for userId={userId}.",
                "No verification code found. Use `/verify` to request one."),

            VerifyCodeResultType.TooManyAttempts  => CommandResult.Failure(
                $"Too many failed attempts for userId={userId}.",
                "Too many failed attempts. You've been blacklisted. Contact administrator."),

            VerifyCodeResultType.UnexpectedError  => CommandResult.GeneralError(
                $"Unexpected cache error for userId={userId}."),

            _ => throw new ArgumentOutOfRangeException(nameof(result), result, null)
        };

        if (result == VerifyCodeResultType.TooManyAttempts)
        {
            // blacklist user
        }

        if (result == VerifyCodeResultType.Success)
        {
            // add user to gh and to dc 
        }
        
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }
    
    
}