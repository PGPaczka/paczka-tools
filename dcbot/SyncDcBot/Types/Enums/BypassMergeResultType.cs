namespace SyncDcBot.Types.Enums;

public enum BypassMergeResultType
{
    Success,
    InvalidUrl,
    InvalidPrNumber,
    NotFound,
    AlreadyClosed,
    AlreadyMerged,
    ForcePushDetected,
    NotMergeable,
    UnexpectedError
}