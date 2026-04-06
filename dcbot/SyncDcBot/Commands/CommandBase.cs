using Discord.Interactions;
using Serilog;
using SyncDcBot.Repositories;

namespace SyncDcBot.Commands;

public abstract class CommandBase(CommandResultStore resultStore) : InteractionModuleBase<SocketInteractionContext>
{
    protected readonly CommandResultStore ResultStore = resultStore;
}