local currentState = redis.call('GET', KEYS[1])

if not currentState then
    redis.call('PSETEX', KEYS[1], ARGV[1], 'PROCESSING')
    return 1
end

if currentState == 'COMPLETED' then
    return 2
end

if currentState == 'PROCESSING' then
    return 3
end

return 3
