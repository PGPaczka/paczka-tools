namespace SyncDcBot.Types;

public enum SendCodeResultType
{
    Success,
    CodeAlreadyPending,
    InvalidEmailFormat,
    EmailDeliveryFailed 
}