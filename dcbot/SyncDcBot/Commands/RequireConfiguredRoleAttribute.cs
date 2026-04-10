using Discord;
using Discord.Interactions;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using PreconditionAttribute = Discord.Interactions.PreconditionAttribute;
using PreconditionResult = Discord.Interactions.PreconditionResult;

namespace SyncDcBot.Commands;

public class RequireConfiguredRoleAttribute : PreconditionAttribute
{
    private readonly string _configKey;

    public RequireConfiguredRoleAttribute(string configKey)
    {
        _configKey = configKey;
    }

    // todo: add role and user ([user] does not belond to [role]
    public override Task<PreconditionResult> CheckRequirementsAsync(
        IInteractionContext context, ICommandInfo command, IServiceProvider services)
    {
        var config = services.GetRequiredService<IConfiguration>();
        var roleId = config[_configKey];

        if (roleId is null)
            return Task.FromResult(PreconditionResult.FromError($"Config key '{_configKey}' not found."));

        if (!ulong.TryParse(roleId, out var roleIdUlong))
            return Task.FromResult(PreconditionResult.FromError($"Invalid role ID in config key '{_configKey}'."));

        var guildUser = context.User as IGuildUser;
        if (guildUser is null)
            return Task.FromResult(PreconditionResult.FromError("This command must be used in a server."));

        return guildUser.RoleIds.Contains(roleIdUlong)
            ? Task.FromResult(PreconditionResult.FromSuccess())
            : Task.FromResult(PreconditionResult.FromError("You don't have the required role."));
    }
}