package com.threadpoollab.controller;

import com.threadpoollab.service.MetricsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

// Metrics on port 8080 as well as 8081/actuator/lab
// Dashboard tries 8081 first (stays up when 8080 is saturated), falls back to 8080
@RestController
@RequestMapping("/metrics")
@CrossOrigin(origins = "*", originPatterns = "*")
public class MetricsController {

    @Autowired
    private MetricsService metricsService;

    @GetMapping("/snapshot")
    public Map<String, Object> snapshot() {
        return metricsService.snapshot();
    }
}
