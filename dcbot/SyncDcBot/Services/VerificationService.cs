using System.Text.RegularExpressions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

//TODO: not finished!
namespace SyncDcBot.Services;

public record VerificationEntry(string Code, 
    string GitHubUsername, 
    DateTimeOffset SentAt, 
    DateTimeOffset ExpiresAt, 
    int Attempts)
{
    public bool IsExpired => DateTimeOffset.UtcNow > ExpiresAt;
    
    public DateTimeOffset GetPolishExpiryTime()
    {
        var polandZone = TimeZoneInfo.FindSystemTimeZoneById("Europe/Warsaw");
        return TimeZoneInfo.ConvertTime(ExpiresAt, polandZone);
    }
    
}

public record SendCodePendingData(VerificationEntry Entry);
public record EmailFailedData(ServiceResult<GmailResultType> Data);

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
    private string GetEmailBody(VerificationEntry entry)
    {
        var localExpiry = GetPolishTime(entry.ExpiresAt);

        return $"Your verification code: {entry.Code}\n" +
               $"Code is valid for {CodeExpiryTime.TotalMinutes} minutes.\n" +
               $"(valid until " +
               $"[{localExpiry:dd.MM.yyyy}] {localExpiry:HH:mm} (local) / " +
               $"[{entry.ExpiresAt:dd.MM.yyyy}] {entry.ExpiresAt:HH:mm} (UTC))";
    }

    public static DateTimeOffset GetPolishTime(DateTimeOffset time)
    {
        var polandZone = TimeZoneInfo.FindSystemTimeZoneById("Europe/Warsaw");
        return TimeZoneInfo.ConvertTime(time, polandZone);
    }

    public VerificationService(GmailSenderService gmailSender, IConfiguration config, IMemoryCache cache)
    {
        _gmailSender = gmailSender;
        _config = config;
        _cache = cache;
    }

    public async Task<ServiceResult<SendCodeResultType>> StartVerification(ulong userId, string userEmail, string githubUsername)
    {
        if (!EmailFormat.IsMatch(userEmail))
        {
            return ServiceResult.Create(SendCodeResultType.InvalidEmailFormat);
        }

        if (_cache.TryGetValue<VerificationEntry>(userId, out var userVerificationEntry) 
            && userVerificationEntry is {IsExpired: false})
        {
            return ServiceResult.CreateWith(
                SendCodeResultType.CodeAlreadyPending,
                new SendCodePendingData(userVerificationEntry)
            );
        }

        var code = GenerateCode();
        
        var utcNow = DateTimeOffset.UtcNow;
        var expirationTime = utcNow.Add(CodeExpiryTime);
        var additionalTtl = TimeSpan.FromHours(1);
        
        var entry = new VerificationEntry(
            Code: code,
            GitHubUsername: githubUsername,
            SentAt: utcNow,
            ExpiresAt: expirationTime,
            Attempts: 0);

        _cache.Set(userId, entry, expirationTime + additionalTtl);

        var gmailResult = await _gmailSender.SendMessage(
            userEmail,
            EmailSubject,
            GetEmailBody(entry)
        );

        if (!gmailResult.IsSuccess)
        {
            return ServiceResult.CreateWith(
                SendCodeResultType.EmailDeliveryFailed,
                new EmailFailedData(gmailResult)
            );
        }

        return ServiceResult.Create(SendCodeResultType.Success);
    }

    // todo: maybe add info, when it expired, how many attempts left
    public VerifyCodeResultType VerifyCode(ulong userId, string code)
    {
        if (!_cache.TryGetValue<VerificationEntry>(userId, out var entry) || entry is null)
        {
            return VerifyCodeResultType.NotFound;
        }

        if (entry.IsExpired)
        {
            return VerifyCodeResultType.Expired;
        }
        
        if (entry.Attempts >= MaxAttempts)
        {
            return VerifyCodeResultType.TooManyAttempts;
        }
        
        if (entry.Code != code)
        {
            var updatedAttempts = entry.Attempts + 1;
            var timeLeftToExpire = entry.ExpiresAt - DateTimeOffset.UtcNow;
            _cache.Set(userId, entry with { Attempts = updatedAttempts }, timeLeftToExpire);
    
            return updatedAttempts >= MaxAttempts
                ? VerifyCodeResultType.TooManyAttempts
                : VerifyCodeResultType.InvalidCode;
        }

        _cache.Remove(userId);
        return VerifyCodeResultType.Success;
    }

    private static string GenerateCode()
    {
        return Random.Shared.Next(100_000, 1_000_000).ToString();
    }
}

