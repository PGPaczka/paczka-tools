using System.Net;
using Discord;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Serilog;
using SyncDcBot.Services;
using SyncDcBot.Services.GitHub;

namespace SyncDcBot.Configuration;

public class BotApplication
{
    private IHost _host = null!;
    private ILogger _logger = null!;
    
    public async Task RunAsync()
    {
        _host = BuildHost();
        _logger = Log.ForContext("Source", "App");
        ValidateConfiguration(_host.Services.GetRequiredService<IConfiguration>());
        await InitializeServicesAsync();
        await StartBotAsync();
    }

    private IHost BuildHost() =>
        Host.CreateDefaultBuilder()
            .ConfigureAppConfiguration(ConfigureApp)
            .ConfigureServices(ServiceRegistry.Register)
            .UseSerilog(SerilogConfiguration.Configure)
            .Build();

    private static void ConfigureApp(IConfigurationBuilder config)
    {
        config.SetBasePath(AppDomain.CurrentDomain.BaseDirectory);
        config.AddJsonFile("Configuration/appsettings.json");
    }

    private async Task InitializeServicesAsync()
    {
        await _host.Services.GetRequiredService<DiscordLoggingService>().InitializeAsync();
        await _host.Services.GetRequiredService<InteractionHandler>().InitializeAsync();
    }

    private async Task StartBotAsync()
    {
        var client = _host.Services.GetRequiredService<DiscordSocketClient>();
        var config = _host.Services.GetRequiredService<IConfiguration>();

        _logger.Information("Token loaded");
        await client.LoginAsync(TokenType.Bot, config["DiscordConfig:BotToken"]);
        await client.StartAsync();
        await _host.RunAsync();
    }

    private void ValidateConfiguration(IConfiguration config)
    {
        var missing = ServiceRegistry.RequiredKeys
            .Where(key => string.IsNullOrEmpty(config[key]))
            .ToList();

        if (missing.Count == 0) return;

        foreach (var key in missing)
            _logger.Fatal("Missing required configuration key: {Key}", key);

        throw new InvalidOperationException($"Missing configuration keys: {string.Join(", ", missing)}");
    }
    
    private void StartHealthCheck()
    {
        var discord = _host.Services.GetRequiredService<DiscordSocketClient>();
        var health = _host.Services.GetRequiredService<HealthService>();
        var config = _host.Services.GetRequiredService<IConfiguration>();
        var url = config["HealthConfig:Url"]!;

        var listener = new HttpListener();
        listener.Prefixes.Add(url);
        listener.Start();

        _ = Task.Run(async () => { await HealthcheckConfiguration.RunHealthCheck(listener, health, discord); });

        _logger.Information("Health check listening on {Url}", url);
    }
}