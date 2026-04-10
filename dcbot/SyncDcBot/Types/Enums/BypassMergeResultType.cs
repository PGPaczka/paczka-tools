namespace SyncDcBot.Types.Enums;

public enum BypassMergeResultType
{
    Success,
    InvalidUrl,
    InvalidPrNumberFormat,
    NotFound,
    AlreadyClosed,
    AlreadyMerged,
    ForcePushDetected,
    NotMergeable,
    UnexpectedError
}