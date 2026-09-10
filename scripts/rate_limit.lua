-- scripts/rate_limit.lua
-- Sliding Window Counter Rate Limiter using Redis Sorted Sets (ZSET)
--
-- KEYS[1]: Rate limit key identifier (e.g., "rate_limit:ip:192.168.1.1")
-- ARGV[1]: Current Unix timestamp in milliseconds (now)
-- ARGV[2]: Window size in milliseconds (window_ms)
-- ARGV[3]: Maximum allowed requests in window (limit)
-- ARGV[4]: Unique member identifier for this request (member_id)
--
-- Returns table: { allowed (0 or 1), remaining_quota, retry_after_seconds }

local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_id = ARGV[4]

-- Calculate the earliest timestamp within the sliding window
local clear_before = now - window_ms

-- 1. Prune all requests older than the sliding window boundary (-inf to clear_before)
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- 2. Count remaining active requests in the current window
local current_requests = tonumber(redis.call('ZCARD', key))

if current_requests < limit then
    -- Quota is available: Record current request timestamp into the ZSET
    redis.call('ZADD', key, now, member_id)
    
    -- Refresh key expiration with 1000ms safety buffer to ensure cleanup if client goes idle
    redis.call('PEXPIRE', key, window_ms + 1000)
    
    local remaining = limit - (current_requests + 1)
    return { 1, remaining, 0 }
else
    -- Quota exceeded: Calculate time until oldest request in current window expires
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after_seconds = 1
    
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        local reset_time = oldest_ts + window_ms
        if reset_time > now then
            retry_after_seconds = math.ceil((reset_time - now) / 1000)
            if retry_after_seconds <= 0 then
                retry_after_seconds = 1
            end
        end
    end

    -- Keep key alive with buffer during rejection bursts to avoid premature eviction
    redis.call('PEXPIRE', key, window_ms + 1000)
    
    return { 0, 0, retry_after_seconds }
end
