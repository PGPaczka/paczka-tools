using Discord;
using Discord.Interactions;
using Serilog;
using SyncDcBot.Repositories;

namespace SyncDcBot.Commands;

public abstract class CommandBase(CommandResultStore resultStore) : InteractionModuleBase<SocketInteractionContext>
{
    protected readonly CommandResultStore ResultStore = resultStore;
    
    protected bool HasRole(string roleIdStr)
    {
        var roleId = ulong.Parse(roleIdStr);
        return ((IGuildUser)Context.User).RoleIds.Contains(roleId);
    }

    protected async Task AddRoleAsync(string roleIdStr)
    {
        var roleId = ulong.Parse(roleIdStr);
        var guildUser = (IGuildUser)Context.User;
        await guildUser.AddRoleAsync(roleId);
    }
}