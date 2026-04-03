using System.Collections.Concurrent;
using Serilog.Events;

namespace SyncDcBot.Repositories;

public record CommandResult(bool Success, string Message, LogEventLevel LogLevel);

public class CommandResultStore
{
    private readonly ConcurrentDictionary<ulong, CommandResult> _results = new();

    public void Set(ulong interactionId, CommandResult result) =>
        _results[interactionId] = result;

    public CommandResult? Take(ulong interactionId)
    {
        _results.TryRemove(interactionId, out var result);
        return result;
    }
}