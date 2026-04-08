using System.Collections.Concurrent;
using Serilog.Events;

namespace SyncDcBot.Repositories;

public enum BotResponseType
{
    None,
    Ephemeral,
    Visible
}

public record CommandResult(
    bool IsSuccess,
    string Message,
    LogEventLevel LogLevel,
    string? UserMessage = null,
    BotResponseType ResponseType = BotResponseType.Ephemeral
)
{
    public static CommandResult Success(string? msg, string? usrMsg = null,
        BotResponseType respondType = BotResponseType.Ephemeral)
        => new(true, msg ?? "OK", LogEventLevel.Information, usrMsg, respondType);

    public static CommandResult Failure(string? msg, string? usrMsg = null,
        BotResponseType respondType = BotResponseType.Ephemeral)
        => new(false, msg ?? "FAIL", LogEventLevel.Warning, usrMsg, respondType);

    public bool ShouldBotRespond()
        => ResponseType != BotResponseType.None;

    public bool ShouldBotRespondEphemeral()
        => ResponseType == BotResponseType.Ephemeral;

    public string GetUserMessage() => UserMessage ?? Message;
}

public class CommandResultStore
{
    private readonly ConcurrentDictionary<ulong, CommandResult> _results = new();

    public void Set(ulong interactionId, CommandResult result) =>
        _results[interactionId] = result;

    public void SetSuccess(
        ulong interactionId,
        string msg,
        string? usrMsg = null,
        BotResponseType responseType = BotResponseType.Ephemeral
    )
        => _results[interactionId] = CommandResult.Success(msg, usrMsg, responseType);

    public void SetFailure(
        ulong interactionId,
        string msg,
        string? usrMsg = null,
        BotResponseType responseType = BotResponseType.Ephemeral
    )
        => _results[interactionId] = CommandResult.Failure(msg, usrMsg, responseType);

    public CommandResult? Take(ulong interactionId)
    {
        _results.TryRemove(interactionId, out var result);
        return result;
    }
}