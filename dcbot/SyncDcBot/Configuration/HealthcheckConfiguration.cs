using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using Discord;
using Discord.WebSocket;
using SyncDcBot.Services.GitHub;

namespace SyncDcBot.Configuration;

public class HealthcheckConfiguration
{
    public static async Task RunHealthCheck(HttpListener listener, HealthService health, DiscordSocketClient discord)
    {
        while (true)
        {
            var ctx = await listener.GetContextAsync();

            var githubOk = await health.PingAsync();
            var discordOk = discord.ConnectionState == ConnectionState.Connected;

            var response = JsonSerializer.Serialize(new
            {
                status = githubOk && discordOk ? "ok" : "degraded",
                timestamp = DateTime.UtcNow,
                uptime = DateTime.UtcNow - Process.GetCurrentProcess().StartTime.ToUniversalTime(),
                services = new
                {
                    discord = discordOk ? "ok" : "disconnected",
                    github = githubOk ? "ok" : "error"
                }
            });

            ctx.Response.StatusCode = githubOk && discordOk ? 200 : 503;
            ctx.Response.ContentType = "application/json";
            var buffer = Encoding.UTF8.GetBytes(response);
            await ctx.Response.OutputStream.WriteAsync(buffer);
            ctx.Response.Close();
        }
    }
}