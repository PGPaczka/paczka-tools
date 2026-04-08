using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Serilog;
using Serilog.Events;
using Serilog.Sinks.SystemConsole.Themes;

namespace SyncDcBot.Configuration;

public static class SerilogConfiguration
{
    private const string DefaultTemplate =
        "[{Timestamp:yyyy-MM-dd HH:mm:ss} {Level:u3}] [{Source}] {Message:lj}{NewLine}{Exception}";

    public static void Configure(HostBuilderContext ctx, LoggerConfiguration log)
    {
        var consoleTemplate = ctx.Configuration["LogsConfig:ConsoleLogTemplate"] ?? DefaultTemplate;
        var fileTemplate    = ctx.Configuration["LogsConfig:FileLogTemplate"] ?? DefaultTemplate;
        var maxLogSize      = ctx.Configuration.GetValue<int>("LogsConfig:MaxLogSizeInMB", 50) * 1024 * 1024;

        log
            .MinimumLevel.Debug()
            .Enrich.WithProperty("Source", "Host")
            .WriteTo.Console(theme: AnsiConsoleTheme.Literate, outputTemplate: consoleTemplate)
            .WriteTo.File(
                path: "logs/all/bot.log",
                fileSizeLimitBytes: maxLogSize,
                rollOnFileSizeLimit: true,
                outputTemplate: fileTemplate)
            .WriteTo.File(
                path: "logs/daily/bot-.log",
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 7,
                outputTemplate: fileTemplate)
            .WriteTo.File(
                path: "logs/errors/errors-.log",
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 30,
                restrictedToMinimumLevel: LogEventLevel.Warning,
                outputTemplate: fileTemplate);
    }
}