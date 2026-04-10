namespace SyncDcBot.Types;

public record ServiceResult<TType>(TType Type, string? Message = null) where TType : Enum
{
    public bool IsSuccess => Equals(Type, GetSuccessValue());
    
    private static TType GetSuccessValue() 
        => (TType)Enum.Parse(typeof(TType), "Success");
}

public record ServiceResult<TType, TData>(TType Type, TData? Data = default, string? Message = null) 
    : ServiceResult<TType>(Type, Message) where TType : Enum;