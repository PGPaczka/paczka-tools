using Serilog.Events;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Types;

public record CommandResult(
    bool IsSuccess,
    string Message,
    LogEventLevel LogLevel,
    string? UserMessage = null,
    BotResponseType ResponseType = BotResponseType.Ephemeral
)
{
    public static string AdminRoleId { get; set; } = string.Empty;
    
    public static CommandResult Success(string? msg, string? usrMsg = null,
        BotResponseType respondType = BotResponseType.Ephemeral)
        => new(true, msg ?? "OK", LogEventLevel.Information, usrMsg, respondType);

    public static CommandResult Failure(string? msg, string? usrMsg = null,
        BotResponseType respondType = BotResponseType.Ephemeral)
        => new(false, msg ?? "FAIL", LogEventLevel.Warning, usrMsg, respondType);

    public static CommandResult Error(string? msg, string? usrMsg = null,
        BotResponseType respondType = BotResponseType.Ephemeral)
        => new(false, msg ?? "ERROR", LogEventLevel.Error, usrMsg, respondType);
    
    public static CommandResult GeneralError(string logMsg)
        => Error(logMsg, $"Something went wrong. Contact the admin (<@&{AdminRoleId}>) for help.");

    public bool ShouldBotRespond()
        => ResponseType != BotResponseType.None;

    public bool ShouldBotRespondEphemeral()
        => ResponseType == BotResponseType.Ephemeral;

    public string GetUserMessage() => UserMessage ?? Message;
}