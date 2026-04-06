using Discord.Interactions;
using Serilog.Events;
using SyncDcBot.Repositories;

namespace SyncDcBot.Commands;

public class GeneralModule(CommandResultStore resultStore) : CommandBase(resultStore)
{
    [SlashCommand("ping", "Check if bot is up")]
    public Task PingAsync()
    {
        ResultStore.SetSuccess(Context.Interaction.Id, $"🏓 Pong! Delay: **{Context.Client.Latency}ms**", BotResponseType.Visible);
        return Task.CompletedTask;
    }
}