namespace SyncDcBot.Types.Enums;

public enum SendCodeResultType
{
    Success,
    CodeAlreadyPending,
    InvalidEmailFormat,
    EmailDeliveryFailed 
}