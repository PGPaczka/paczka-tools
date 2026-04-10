using System.Collections.Concurrent;
using SyncDcBot.Types;
using SyncDcBot.Types.Enums;

namespace SyncDcBot.Repositories;

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

    public void SetError(
        ulong interactionId,
        string msg,
        string? usrMsg = null,
        BotResponseType responseType = BotResponseType.Ephemeral
    )
        => _results[interactionId] = CommandResult.Error(msg, usrMsg, responseType);
    
    public CommandResult? Take(ulong interactionId)
    {
        _results.TryRemove(interactionId, out var result);
        return result;
    }
}