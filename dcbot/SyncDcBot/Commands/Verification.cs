using Discord.Interactions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Repositories;
using SyncDcBot.Services;
using SyncDcBot.Services.GitHub;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;
using OneOf;

namespace SyncDcBot.Commands;

public class VerificationModule(
    CommandResultStore resultStore,
    VerificationService verificationService,
    AddToRepoService  addToRepoService,
    IConfiguration configuration,
    IMemoryCache cache) : CommandBase(resultStore)
{
    [SlashCommand("ping", "Check if bot is up")]
    
    public async Task PingAsync()
    {
        ResultStore.SetSuccess(Context.Interaction.Id, $"🏓 Pong! Delay: **{Context.Client.Latency}ms**",
            responseType: BotResponseType.Visible);
    }

    [SlashCommand("verify", "Send verification code")]
    public async Task VerifyAsync(
        [Summary("email", "Your student email")] string email,
        [Summary("github-profile-link", "Link to your GitHub profile")] string githubProfileLink)
    {
        await Context.Interaction.DeferAsync(ephemeral: true);
        var userDiscordId = Context.User.Id;
        
        var roleCheckResult = WereRolesAlreadyApplied(Context.User.Id);
        if (roleCheckResult != null)
        {
            ResultStore.Set(Context.Interaction.Id, roleCheckResult);
            return;
        }
        
        var result = await StartVerification(email, githubProfileLink, userDiscordId);
        var commandResult = ConvertSendCodeResultToCommandResult(email, result, userDiscordId);
        
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }

    [SlashCommand("code", "Submit your verification code")]
    public async Task VerifyCodeAsync(
        [Summary("code", "Verification code sent to your email")] string code)
    {
        await Context.Interaction.DeferAsync(ephemeral: true);
        var userId = Context.User.Id;
        
        var roleCheckResult = WereRolesAlreadyApplied(userId);
        if (roleCheckResult != null)
        {
            ResultStore.Set(Context.Interaction.Id, roleCheckResult);
            return;
        }

        cache.TryGetValue<VerificationEntry>(userId, out var entry);
        var result = verificationService.VerifyCode(userId, code);
        var commandResult = await ApplyVerificationEffectsAsync(result, userId, entry);
        
        ResultStore.Set(Context.Interaction.Id, commandResult);
    }
    
    private async Task<OneOf<ServiceResult<SendCodeResultType>, ServiceResult<GitHubResultType>>> StartVerification(
        string email, string githubProfileLink, ulong userDiscordId)
    {
        if (!AddToRepoService.TryParseGitHubLogin(githubProfileLink, out var ghUser))
        {
            return ServiceResult.Create(GitHubResultType.UserNotFound, $"Invalid GitHub profile link `{githubProfileLink}`");
        }

        var result = await verificationService.StartVerification(userDiscordId, email, ghUser);
        return result;
    }

    private CommandResult ConvertSendCodeResultToCommandResult(
        string email,
        OneOf<ServiceResult<SendCodeResultType>, ServiceResult<GitHubResultType>> result,
        ulong userDiscordId)
    {
        var codeExpiryTime = TimeSpan.FromMinutes(
            configuration.GetValue<int>("DiscordConfig:VerificationCodeExpiryMinutes", 15));
        var emailDomain = configuration.GetValue<string>("DiscordConfig:StudentEmailDomain")!;

        return result.Match(
            sendCodeResult =>
            {
                var pendingData  = (sendCodeResult as ServiceResult<SendCodeResultType, SendCodePendingData>)?.Data;
                var emailFailData = (sendCodeResult as ServiceResult<SendCodeResultType, EmailFailedData>)?.Data;

                return sendCodeResult.Type switch
                {
                    SendCodeResultType.Success            => CommandResult.Success(
                        $"Verification email sent to {email}",
                        $"Verification code sent to `{email}`. Code is valid for {codeExpiryTime.TotalMinutes} minutes."),

                    SendCodeResultType.CodeAlreadyPending => CommandResult.Failure(
                        $"Code already sent to {email} at {pendingData!.Entry.SentAt}.",
                        $"Code already sent. Check your inbox. If you can't find it, wait until {pendingData!.Entry.GetPolishExpiryTime():HH:mm} and try again."),

                    SendCodeResultType.InvalidEmailFormat => CommandResult.Failure(
                        $"Invalid email format for userId={userDiscordId}: {email}",
                        $"Email must be in format `s123456{emailDomain}`"),

                    SendCodeResultType.EmailDeliveryFailed => ConvertGmailResultToCommandResult(emailFailData!.Data, email),

                    _ => throw new ArgumentOutOfRangeException(nameof(sendCodeResult.Type), sendCodeResult.Type, null)
                };
            },
            githubResult => githubResult.Type switch
            {
                GitHubResultType.UserNotFound   => CommandResult.Failure(
                    githubResult.Message,
                    "Invalid GitHub profile link. Expected: `https://github.com/username`"),
                
                _ => throw new ArgumentOutOfRangeException(nameof(githubResult.Type), githubResult.Type, null)
            });
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
            _                                   => throw new ArgumentOutOfRangeException(nameof(result.Type), result.Type, null)
        };
        return commandResult;
    }

    private async Task<CommandResult> ApplyVerificationEffectsAsync (
        VerifyCodeResultType result, ulong userId, VerificationEntry? entry)
    {
        var commandResult = ConvertVerifyCodeResultToCommandResult(result, userId);
        
        switch (result)
        {
            case VerifyCodeResultType.TooManyAttempts:
                await AddRoleAsync(configuration["DiscordConfig:BlacklistedRoleId"]!);
                return commandResult;
            case VerifyCodeResultType.Success:
                await AddRoleAsync(configuration["DiscordConfig:VerifiedRoleId"]!);
                break;
            default: 
                return commandResult;
        }

        var ghResult = await addToRepoService.AddCollaboratorAsync(entry?.GitHubUsername);
        if (!ghResult.IsSuccess)
        {
            return CommandResult.Failure(
                $"Verified userId={userId} but failed to add {entry!.GitHubUsername} to GitHub: {ghResult.Message}",
                "You've been verified on Discord, but there was an issue adding you to GitHub. Contact an admin."
            );
        }

        return commandResult;
    }

    private CommandResult? WereRolesAlreadyApplied(ulong userId)
    {
        if (HasRole(configuration["DiscordConfig:VerifiedRoleId"]!))
        {
            return CommandResult.Failure(
                $"User {Context.User.Username} ({userId}) attempted to verify but is already verified.",
                "You are already verified."
            );
        }

        if (HasRole(configuration["DiscordConfig:BlacklistedRoleId"]!))
        {
            return CommandResult.Failure(
                $"Blacklisted user {Context.User.Username} ({userId}) attempted to verify.",
                "You are blacklisted and cannot verify."
            );
        }

        return null;
    }

    private CommandResult ConvertVerifyCodeResultToCommandResult(VerifyCodeResultType result, ulong userId)
    {
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
        return commandResult;
    }
}