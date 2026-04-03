using Discord.Interactions;
using Discord.WebSocket;
using Serilog;
using Serilog.Events;

namespace SyncDcBot.Services;

// logs stricte technical discord info
public class DiscordLoggingService
{
    private readonly DiscordSocketClient _discordClient;
    private readonly InteractionService _interactions;

    public DiscordLoggingService(
        DiscordSocketClient discordClient,
        InteractionService interactions)
    {
        _discordClient = discordClient;
        _interactions = interactions;
    }

    public Task InitializeAsync()
    {
        _discordClient.Log += OnLog;
        _interactions.Log += OnLog;
        return Task.CompletedTask;
    }

    // todo: check what it does
    private Task OnLog(Discord.LogMessage log)
    {
        // GatewayReconnectException is a normal flow, supress it
        if (log.Exception is GatewayReconnectException)
        {
            Log.ForContext("Source", log.Source)
                .Debug("Server requested a reconnect");
            return Task.CompletedTask;
        }
        
        var level = ConvertEventDiscordToSerilog(log.Severity);
        Log.ForContext("Source", log.Source)
            .Write(level, log.Exception, "{Message}", log.Message ?? log.Exception?.Message ?? "Unknown error");
        return Task.CompletedTask;
    }

    // Bridge: Discord.LogSeverity → Serilog.LogEventLevel
    private LogEventLevel ConvertEventDiscordToSerilog(Discord.LogSeverity severity)
    {
        return severity switch
        {
            Discord.LogSeverity.Critical => LogEventLevel.Fatal,
            Discord.LogSeverity.Error    => LogEventLevel.Error,
            Discord.LogSeverity.Warning  => LogEventLevel.Warning,
            Discord.LogSeverity.Info     => LogEventLevel.Information,
            Discord.LogSeverity.Verbose  => LogEventLevel.Debug,
            Discord.LogSeverity.Debug    => LogEventLevel.Verbose,
            _                    => LogEventLevel.Information
        };
    }
}