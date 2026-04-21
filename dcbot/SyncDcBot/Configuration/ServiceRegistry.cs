using Discord;
using Discord.Interactions;
using Discord.WebSocket;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Octokit;
using SyncDcBot.Repositories;
using SyncDcBot.Services;
using SyncDcBot.Services.GitHub;
using SyncDcBot.Types;

namespace SyncDcBot.Configuration;

public static class ServiceRegistry
{
    public static readonly string[] RequiredKeys =
    [
        "DiscordConfig:BotToken",
        "DiscordConfig:GuildId",
        "DiscordConfig:LogChannelId",
        "DiscordConfig:AdminRoleId",
        "DiscordConfig:VerifiedRoleId",
        "DiscordConfig:BlacklistedRoleId",
        "DiscordConfig:StudentEmailDomain",
        
        "GitHubConfig:GitHubToken",
        "GitHubConfig:RepoOwner",
        "GitHubConfig:RepoName",
        
        "GCC:GmailConfig:GmailCredentials:installed:client_id",
        "GCC:GmailConfig:GmailCredentials:installed:client_secret",
        // "GCC:GmailConfig:GmailToken:RefreshToken" // required only in production (after first launch)
    
        "HealthConfig:Url"
    ];
    
    public static void Register(HostBuilderContext ctx, IServiceCollection services)
    {
        services
            .AddMemoryCache();
            
        AddDiscord(ctx.Configuration, services);
        AddGitHub(ctx.Configuration, services);

        services
            .AddSingleton<InteractionHandler>()
            .AddSingleton<DiscordLoggingService>()
            .AddSingleton<CommandResultStore>()
            .AddSingleton<AddToRepoService>()
            .AddSingleton<BypassPrRulesService>()
            .AddSingleton<GmailSenderService>()
            .AddSingleton<VerificationService>()
            .AddSingleton<HealthService>();
    }

    private static void AddDiscord(IConfiguration config, IServiceCollection services)
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
        
        CommandResult.AdminRoleId = config["DiscordConfig:AdminRoleId"]!;
    }

    private static void AddGitHub(IConfiguration config, IServiceCollection services)
    {
        services.AddSingleton(_ => new GitHubClient(new ProductHeaderValue("SyncDcBot"))
        {
            Credentials = new Credentials(config["GitHubConfig:GitHubToken"])
        });
    }
}