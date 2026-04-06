using Discord;
using Discord.Interactions;
using Discord.WebSocket;
using Serilog;
using Serilog.Events;

namespace SyncDcBot.Services;

// logs strict technical discord info
public class DiscordLoggingService
{
    private readonly DiscordSocketClient _discordClient;
    private readonly InteractionService _interactions;
    
    private Exception? _lastException;
    private DateTime _lastExceptionTime = DateTime.MinValue;
    private static readonly TimeSpan DuplicateWindow = TimeSpan.FromMinutes(1);

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

    private Task OnLog(LogMessage log)
    {
        var logger = Log.ForContext("Source", log.Source);
        var level  = ConvertSeverityDiscordToSerilog(log.Severity);

        if (log.Exception is GatewayReconnectException)
        {
            logger.Debug("Server requested a reconnect");
            return Task.CompletedTask;
        }

        if (log.Exception is not null && IsDuplicateException(log.Exception))
        {
            logger.Write(level, "(repeated) {Message}", log.Exception.Message);
            return Task.CompletedTask;
        }

        logger.Write(level, log.Exception,
            "{Message}", log.Message ?? log.Exception?.Message ?? "Unknown error");

        return Task.CompletedTask;
    }

    private bool IsDuplicateException(Exception exception)
    {
        var now = DateTime.UtcNow;
        var isDuplicate = exception.Message == _lastException?.Message
                          && now - _lastExceptionTime < DuplicateWindow;

        _lastException     = exception;
        _lastExceptionTime = now;

        return isDuplicate;
    }

    // Bridge: Discord.LogSeverity → Serilog.LogEventLevel
    private LogEventLevel ConvertSeverityDiscordToSerilog(Discord.LogSeverity severity)
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