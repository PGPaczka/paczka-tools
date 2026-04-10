using System.Text.RegularExpressions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

//TODO: not finished!
namespace SyncDcBot.Services;

public record VerificationEntry(string Code, DateTimeOffset SentAt, DateTimeOffset ExpiresAt, int Attempts)
{
    public bool IsExpired => DateTimeOffset.UtcNow > ExpiresAt;
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
        var polandZone = TimeZoneInfo.FindSystemTimeZoneById("Europe/Warsaw");
        var localExpiry = TimeZoneInfo.ConvertTime(entry.ExpiresAt, polandZone);

        return $"Your verification code: {entry.Code}\n" +
               $"Code is valid for {CodeExpiryTime.TotalMinutes} minutes.\n" +
               $"(valid until " +
               $"[{localExpiry:dd.MM.yyyy}] {localExpiry:HH:mm} (local) / " +
               $"[{entry.ExpiresAt:dd.MM.yyyy}] {entry.ExpiresAt:HH:mm} (UTC))";
    }
    
    public VerificationService(GmailSenderService gmailSender, IConfiguration config, IMemoryCache cache)
    {
        _gmailSender = gmailSender;
        _config = config;
        _cache = cache;
    }

    public async Task<ServiceResult<SendCodeResultType>> StartVerification(ulong userId, string userEmail)
    {
        if (!EmailFormat.IsMatch(userEmail))
        {
            return ServiceResult.Create(SendCodeResultType.InvalidEmailFormat);
        }

        if (_cache.TryGetValue<VerificationEntry>(userId, out var userVerificationEntry))
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
        
        var entry = new VerificationEntry(code, utcNow,expirationTime, Attempts: 0);
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
        if (!_cache.TryGetValue<VerificationEntry>(userId, out var entry))
        {
            return VerifyCodeResultType.NotFound;
        }

        if (entry is null)
        {
            return VerifyCodeResultType.UnexpectedError;
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
            _cache.Set(userId, entry with { Attempts = entry.Attempts + 1 }, entry.ExpiresAt - DateTimeOffset.UtcNow);
            return entry.Attempts + 1 >= MaxAttempts
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

