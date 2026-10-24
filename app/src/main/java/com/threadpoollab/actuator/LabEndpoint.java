package com.threadpoollab.actuator;

import com.threadpoollab.service.MetricsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;
import java.util.Map;

@Component
@Endpoint(id = "lab")
public class LabEndpoint {
    @Autowired private MetricsService metricsService;

    @ReadOperation
    public Map<String,Object> metrics() { return metricsService.snapshot(); }
}
