using Discord.Interactions;
using SyncDcBot.Commands.Modules;

namespace SyncDcBot.Commands;

public class GeneralModule : CommandBase
{
    [SlashCommand("ping", "Check if bot is up")]
    public async Task PingAsync()
    {
        await RespondAsync($"🏓 Pong! Delay: **{Context.Client.Latency}ms**");
    }
}