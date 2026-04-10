using System.Text.RegularExpressions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Repositories;


//TODO: not finished!
namespace SyncDcBot.Services;

public enum VerifyCodeResult
{
    Success,
    NotFound,
    Expired,
    InvalidCode,
    TooManyAttempts,
    Error
}

public enum SendCodeResultType
{
    Success,
    AlreadySent,
    InvalidEmailFormat,
    EmailFailed
}

public record VerificationEntry(string Code, DateTimeOffset SentAt, DateTimeOffset ExpiresAt, int Attempts)
{
    public bool IsExpired => DateTimeOffset.UtcNow > ExpiresAt;
}

public record SendCodeResult(SendCodeResultType Type, string? ErrorMessage = null)
{
    public static SendCodeResult Success()                          => new(SendCodeResultType.Success);
    public static SendCodeResult AlreadySent()                      => new(SendCodeResultType.AlreadySent);
    public static SendCodeResult InvalidEmailFormat(string message) => new(SendCodeResultType.InvalidEmailFormat);
    public static SendCodeResult EmailFailed(string message)        => new(SendCodeResultType.EmailFailed, message);
}

public class VerificationService
{
    private readonly IMemoryCache _cache;
    private readonly GmailSenderService _gmailSender;
    private readonly IConfiguration _config;

    private TimeSpan CodeExpiryTime => TimeSpan.FromMinutes(
        _config.GetValue<int>("DiscordConfig:VerificationCodeExpiryMinutes", 15));
    private int MaxAttempts =>  _config.GetValue<int>("DiscordConfig:MaxFailedVerificationAttempts", 5);
    private string EmailDomain => _config.GetValue<string>("DiscordConfig:StudentEmailDomain")!;
    private static readonly Regex EmailFormat = new(@"^s\d{6}@student\.pg\.edu\.pl$", RegexOptions.Compiled);
    
    private const string EmailSubject = "PG Paczka Verification Code";
    private string GetEmailBody(VerificationEntry entry) =>
        $"Your verification code: {entry.Code}\n" +
        $"Code is valid for {CodeExpiryTime.TotalMinutes} minutes.\n" +
        $"({entry.ExpiresAt})";
    
    public VerificationService(GmailSenderService gmailSender, IConfiguration config, IMemoryCache cache)
    {
        _gmailSender = gmailSender;
        _config = config;
        _cache = cache;
    }

    public async Task<CommandResult> StartVerification(ulong userId, string userEmail)
    {
        if (!EmailFormat.IsMatch(userEmail))
        {
            return CommandResult.Failure(
                $"Invalid email format for userId={userId}: {userEmail}",
                usrMsg: $"Email must be in format `s123456{EmailDomain}`");
        }

        var utcNow = DateTimeOffset.UtcNow;
        if (_cache.TryGetValue<VerificationEntry>(userId, out var userVerification))
        {
            return CommandResult.Failure(
                $"Code has already been sent to {userEmail} at {userVerification.SentAt}.",
                usrMsg: $"Code has been already sent. Check your inbox/junk folder. If you can't find it, wait until {userVerification.ExpiresAt} and try again");
        }

        var code = GenerateCode();
        var expirationTime = utcNow.Add(CodeExpiryTime);
        var entry = new VerificationEntry(code, utcNow,expirationTime, Attempts: 0);
        _cache.Set(userId, entry, expirationTime + TimeSpan.FromHours(1));

        var result = await _gmailSender.SendMessage(
            userEmail,
            EmailSubject,
            GetEmailBody(entry)
        );

        if (!result.Success)
        {
            return CommandResult.Failure(
                $"Failed to send verification email to {userEmail}: {result.Message}",
                usrMsg: "Failed to send verification email. Try again later.");
        }

        return CommandResult.Success(
            $"Verification email sent to {userEmail}",
            usrMsg: $"Verification code sent to `{userEmail}`. Code is valid for {CodeExpiryTime.TotalMinutes} minutes.",
            respondType: BotResponseType.Ephemeral);
    }

    public VerifyCodeResult VerifyCode(ulong userId, string code)
    {
        if (!_cache.TryGetValue<VerificationEntry>(userId, out var entry))
        {
            return VerifyCodeResult.NotFound;
        }

        if (entry is null)
        {
            return VerifyCodeResult.Error;
        }
        
        if (entry.IsExpired)
        {
            return VerifyCodeResult.Expired;
        }
        
        if (entry.Attempts >= MaxAttempts)
        {
            return VerifyCodeResult.TooManyAttempts;
        }

        if (entry.Code != code)
        {
            _cache.Set(userId, entry with { Attempts = entry.Attempts + 1 }, entry.ExpiresAt - DateTimeOffset.UtcNow);
            return entry.Attempts + 1 >= MaxAttempts
                ? VerifyCodeResult.TooManyAttempts
                : VerifyCodeResult.InvalidCode;
        }

        _cache.Remove(userId);
        return VerifyCodeResult.Success;
    }

    private static string GenerateCode()
    {
        return Random.Shared.Next(100_000, 1_000_000).ToString();
    }
}

