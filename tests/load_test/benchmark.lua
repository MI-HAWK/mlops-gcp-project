-- WRK benchmark script for testing FastAPI /predict endpoint
-- Simulates a typical payload sent to the model inference service

wrk.method = "POST"
wrk.body = '{"airline":"Vistara","source_city":"Delhi","departure_time":"Morning","stops":"one","arrival_time":"Afternoon","destination_city":"Mumbai","class_type":"Business","duration":5.5,"days_left":15}'
wrk.headers["Content-Type"] = "application/json"

-- Optional: function to generate dynamic payloads if needed for drift testing
-- function request()
--    -- randomize payload here
--    return wrk.format(nil, nil, nil, body)
-- end

function response(status, headers, body)
   if status ~= 200 then
      print("Warning: HTTP " .. status .. " - " .. body)
   end
end
