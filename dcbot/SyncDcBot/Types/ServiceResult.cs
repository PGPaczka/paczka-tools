namespace SyncDcBot.Types;

public record ServiceResult<TType>(TType Type, string? Message = null) where TType : Enum
{
    public bool IsSuccess => Equals(Type, GetSuccessValue());

    public static ServiceResult<TType> Create(TType type, string? message = null)
        => new(type, message);

    private static TType GetSuccessValue()
        => (TType)Enum.Parse(typeof(TType), "Success");

    static ServiceResult()
    {
        if (!Enum.IsDefined(typeof(TType), "Success"))
        {
            throw new InvalidOperationException(
                $"{typeof(TType).Name} must define a 'Success' value to be used with ServiceResult.");
        }
    }
}

public record ServiceResult<TType, TData>(TType Type, TData? Data = default, string? Message = null)
    : ServiceResult<TType>(Type, Message) where TType : Enum
{
    public static ServiceResult<TType, TData> Create(TType type, TData? data = default, string? message = null)
        => new(type, data, message);
}

public static class ServiceResult
{
    public static ServiceResult<TType> Create<TType>(TType type, string? message = null) where TType : Enum
        => ServiceResult<TType>.Create(type, message);

    public static ServiceResult<TType, TData> CreateWith<TType, TData>(TType type, TData? data = default,
        string? message = null) where TType : Enum
        => ServiceResult<TType, TData>.Create(type, data, message);

    public static ServiceResult<TType, TData> CreateWithDefault<TType, TData>(TType type,
        string? message = null) where TType : Enum
        => CreateWith<TType, TData>(type, message: message);
}