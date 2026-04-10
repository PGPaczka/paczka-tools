namespace SyncDcBot.Types;

public enum VerifyCodeResultType
{
    Success,
    NotFound,
    Expired,
    InvalidCode,
    TooManyAttempts,
    UnexpectedError
}