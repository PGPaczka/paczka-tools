namespace SyncDcBot.Types;

public enum GmailResultType
{
    Success, 
    RecipientNotFound,
    RateLimitExceeded,
    Unauthorized,
    UnexpectedError
}

// public class GmailResultToCommandResultConverter : ICommandResultConverter<ServiceResult<GmailResultType>>
// {
//     public static CommandResult Covert(ServiceResult<GmailResultType> result)
//     {
//         return result.Type switch
//         {
//             GmailResultType.Success => CommandResult.Success(
//                 $"Message sent successfully to {recipientEmail}"), // skąd wziąc recipientEmail? result.Message?
//             GmailResultType.Failed => CommandResult.Failure($"Google API error: {result.Message}"),
//             GmailResultType.Error => CommandResult.Failure($"Unexpected error: {result.Message}"),
//             _ => CommandResult.Failure(result.Message)
//         };
//     }
// }