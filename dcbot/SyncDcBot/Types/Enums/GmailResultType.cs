namespace SyncDcBot.Types.Enums;

public enum GmailResultType
{
    Success, 
    RecipientNotFound,
    RateLimitExceeded,
    Unauthorized,
    UnexpectedError
}