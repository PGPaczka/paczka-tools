using System.Net;
using System.Text;
using Google.Apis.Auth.OAuth2;
using Google.Apis.Auth.OAuth2.Responses;
using Google.Apis.Gmail.v1;
using Google.Apis.Services;
using Google.Apis.Util.Store;
using Microsoft.Extensions.Configuration;
using SyncDcBot.Test.Services;
using SyncDcBot.Types;

namespace SyncDcBot.Services;

public class GmailSenderService(IConfiguration configuration)
{
    private const string ApplicationName = "PaczkaVerify";
    private const string UserId = "me";

    public async Task<ServiceResult<GmailResultType>> SendMessage(string recipientEmail, string subject, string body)
    {
        try
        {
            var service = await CreateService();
            var message = CreateMessage(recipientEmail, subject, body);
            await service
                .Users
                .Messages
                .Send(message, UserId)
                .ExecuteAsync();
            
            return new ServiceResult<GmailResultType>(GmailResultType.Success);
        }
        catch (Google.GoogleApiException ex)
        {
            var type = ex.HttpStatusCode switch
            {
                HttpStatusCode.TooManyRequests  => GmailResultType.RateLimitExceeded,
                HttpStatusCode.NotFound         => GmailResultType.RecipientNotFound,
                HttpStatusCode.Unauthorized     => GmailResultType.Unauthorized,
                HttpStatusCode.Forbidden        => GmailResultType.Unauthorized,
                _                               => GmailResultType.UnexpectedError
            };
    
            return new ServiceResult<GmailResultType>(type, ex.Error.Message);
        }
        catch (Exception ex)
        {
            return new ServiceResult<GmailResultType>(GmailResultType.UnexpectedError, ex.Message);
        }
    }

    private async Task<GmailService> CreateService()
    {
        var secrets = new ClientSecrets
        {
            ClientId = configuration["GCC:GmailConfig:GmailCredentials:installed:client_id"],
            ClientSecret = configuration["GCC:GmailConfig:GmailCredentials:installed:client_secret"]
        };
        
        if (string.IsNullOrEmpty(secrets.ClientId) || string.IsNullOrEmpty(secrets.ClientSecret))
        {
            throw new ArgumentException("No Gmail secret in appsettings.json");
        }
        
        var tokenResponse = configuration.GetSection("GCC:GmailConfig:GmailToken").Get<TokenResponse>();
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
            var isDevelopment = configuration["Environment"] == "Development";
            tokenDataStore = isDevelopment
                ? new PrintTokenDataStore()
                : throw new ArgumentException("No refresh token found in appsettings.json on Production Environment");
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