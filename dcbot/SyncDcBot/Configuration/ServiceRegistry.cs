using Discord;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Octokit;
using SyncDcBot.Repositories;
using SyncDcBot.Services;

namespace SyncDcBot.Configuration;

public static class ServiceRegistry
{
    public static readonly string[] RequiredKeys =
    [
        "BotToken", 
        "GitHubToken", 
        "GuildId",
        "RepoOwner", 
        "RepoName", 
        "AdminRoleId",
        "LogChannelId"
    ];

    public static void Register(HostBuilderContext ctx, IServiceCollection services)
    {
        AddDiscord(services);
        AddGitHub(ctx.Configuration, services);
        services
            .AddSingleton<InteractionHandler>()
            .AddSingleton<DiscordLoggingService>()
            .AddSingleton<AddToRepoService>()
            .AddSingleton<CommandResultStore>();
    }

    private static void AddDiscord(IServiceCollection services)
    {
        services.AddSingleton(new DiscordSocketClient(new DiscordSocketConfig
        {
            GatewayIntents = GatewayIntents.Guilds
                             | GatewayIntents.GuildMessages
                             | GatewayIntents.MessageContent
                             | GatewayIntents.GuildMembers,
            LogLevel = LogSeverity.Info
        }));

        services.AddSingleton(provider =>
        {
            var client = provider.GetRequiredService<DiscordSocketClient>();
            return new InteractionService(client, new InteractionServiceConfig
            {
                LogLevel = LogSeverity.Info,
                DefaultRunMode = RunMode.Async
            });
        });
    }

    private static void AddGitHub(IConfiguration config, IServiceCollection services)
    {
        services.AddSingleton(_ => new GitHubClient(new ProductHeaderValue("SyncDcBot"))
        {
            Credentials = new Credentials(config["GitHubToken"])
        });
    }
}