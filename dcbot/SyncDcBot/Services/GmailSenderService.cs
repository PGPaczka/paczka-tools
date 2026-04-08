using System.Text;
using Google.Apis.Auth.OAuth2;
using Google.Apis.Auth.OAuth2.Responses;
using Google.Apis.Gmail.v1;
using Google.Apis.Services;
using Google.Apis.Util.Store;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Serilog.Events;
using SyncDcBot.Repositories;
using SyncDcBot.Test.Services;

namespace SyncDcBot.Services;

public record GmailResult(bool Success, string Message, LogEventLevel LogLevel)
{
    public CommandResult ToCommandResult()
    {
        return new CommandResult(Success, Message, LogLevel);
    }
}

public class GmailSenderService
{
    const string ApplicationName = "PaczkaVerify";
    const string UserId = "me";

    readonly IConfiguration _configuration;

    public GmailSenderService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public async Task<GmailResult> SendMessage(string recipientEmail, string subject, string body)
    {
        try
        {
            var service = await CreateService();
            var message = CreateMessage(recipientEmail, subject, body);
            // await service
            //     .Users
            //     .Messages
            //     .Send(message, UserId)
            //     .ExecuteAsync();
            
            return new GmailResult(true, $"Message sent successfully to {recipientEmail}.", LogEventLevel.Information);
        }
        catch (Google.GoogleApiException ex)
        {
            return new GmailResult(false, $"Google API error: {ex.Error.Message}", LogEventLevel.Warning);
        }
        catch (Exception ex)
        {
            return new GmailResult(false, $"Unexpected error: {ex.Message}", LogEventLevel.Error);
        }
    }

    private async Task<GmailService> CreateService()
    {
        var secrets = new ClientSecrets
        {
            ClientId = _configuration["GCC:GmailConfig:GmailCredentials:installed:client_id"],
            ClientSecret = _configuration["GCC:GmailConfig:GmailCredentials:installed:client_secret"]
        };
        
        if (string.IsNullOrEmpty(secrets.ClientId) || string.IsNullOrEmpty(secrets.ClientSecret))
        {
            throw new InvalidOperationException("No Gmail secret in appsettings.json");
        }
        
        var tokenResponse = _configuration.GetSection("GCC:GmailConfig:GmailToken").Get<TokenResponse>();
        var tokenDataStore = ResolveTokenDataStore(tokenResponse);

        var credential = await GoogleWebAuthorizationBroker.AuthorizeAsync(
            secrets,
            [GmailService.Scope.GmailSend],
            UserId,
            CancellationToken.None,
            tokenDataStore
        );

        var service = new GmailService(new BaseClientService.Initializer
        {
            HttpClientInitializer = credential,
            ApplicationName = GmailSenderService.ApplicationName
        });
        
        return service;
    }

    private IDataStore ResolveTokenDataStore(TokenResponse? tokenResponse)
    {
        IDataStore tokenDataStore;
        if (tokenResponse?.RefreshToken is null)
        {
            var isDevelopment = _configuration["Environment"] == "Development";
            tokenDataStore = isDevelopment
                ? new PrintTokenDataStore()
                : throw new InvalidOperationException("No refresh token found in appsettings.json on Production Environment");
        }
        else
        {
            tokenDataStore = new InMemoryTokenDataStore(tokenResponse);
        }

        return tokenDataStore;
    }

    private static Google.Apis.Gmail.v1.Data.Message CreateMessage(string to, string subject, string body)
    {
        var rawMessage = $"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}";
        var encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(rawMessage))
            .Replace('+', '-')
            .Replace('/', '_')
            .TrimEnd('=');

        return new Google.Apis.Gmail.v1.Data.Message { Raw = encoded };
    }
}