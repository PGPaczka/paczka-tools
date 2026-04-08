using System.Text.Json;
using Google.Apis.Util.Store;

namespace SyncDcBot.Test.Services;

class PrintTokenDataStore : IDataStore
{
    public Task StoreAsync<T>(string key, T value)
    {
        Console.WriteLine("Paste into appsettings.json as \"GmailToken\":");
        Console.WriteLine(JsonSerializer.Serialize(value));
        return Task.CompletedTask;
    }

    public Task<T> GetAsync<T>(string key) => Task.FromResult(default(T));
    public Task ClearAsync() => Task.CompletedTask;
    public Task DeleteAsync<T>(string key) => Task.CompletedTask;
}

