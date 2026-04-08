using Google.Apis.Auth.OAuth2.Responses;
using Google.Apis.Util.Store;

namespace SyncDcBot.Test.Services;

class InMemoryTokenDataStore : IDataStore
{
    private TokenResponse _token;

    public InMemoryTokenDataStore(TokenResponse token)
    {
        _token = token;
    }

    public Task<T> GetAsync<T>(string key)
    {
        return Task.FromResult((T)(object)_token);
    }

    public Task StoreAsync<T>(string key, T value)
    {
        if (value is TokenResponse token)
            _token = token;
        return Task.CompletedTask;
    }

    public Task ClearAsync() => Task.CompletedTask;
    public Task DeleteAsync<T>(string key) => Task.CompletedTask;
}