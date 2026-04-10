namespace SyncDcBot.Types.Enums;

public enum VerifyCodeResultType
{
    Success,
    NotFound,
    Expired,
    InvalidCode,
    TooManyAttempts,
    UnexpectedError
}