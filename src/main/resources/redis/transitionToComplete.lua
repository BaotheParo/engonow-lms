local currentState = redis.call('GET', KEYS[1])

if currentState ~= 'PROCESSING' then
    return 0
end

local remainingTtl = redis.call('PTTL', KEYS[1])
if remainingTtl <= 0 then
    remainingTtl = tonumber(ARGV[1])
end

redis.call('PSETEX', KEYS[1], remainingTtl, 'COMPLETED')
return 1
