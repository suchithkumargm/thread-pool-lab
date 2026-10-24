package com.threadpoollab.service;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class MetricsService {
    @Autowired private MeterRegistry registry;
    @Value("${server.tomcat.threads.max:200}") private int configuredMaxThreads;

    public Map<String,Object> snapshot() {
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("ts", System.currentTimeMillis());
        // Thread pool — tomcat.threads.* not registered when management.server.port differs;
        // http.server.requests.active (ACTIVE_TASKS) is the reliable alternative
        m.put("threads_max",     configuredMaxThreads);
        m.put("threads_current", activeRequests() + gauge("jvm.threads.live", 0));
        m.put("threads_busy",    activeRequests());
        // DB pool (HikariCP)
        m.put("db_pool_max",     gauge("hikaricp.connections.max", 0));
        m.put("db_pool_active",  gauge("hikaricp.connections.active", 0));
        m.put("db_pool_idle",    gauge("hikaricp.connections.idle", 0));
        m.put("db_pool_pending", gauge("hikaricp.connections.pending", 0));
        // System
        m.put("cpu_process", gauge("process.cpu.usage", 0.0));
        m.put("cpu_system",  gauge("system.cpu.usage", 0.0));
        m.put("jvm_threads", gauge("jvm.threads.live", 0));
        m.put("virtual_threads", Thread.currentThread().isVirtual());
        return m;
    }

    private double activeRequests() {
        try { return registry.get("http.server.requests.active").longTaskTimer().activeTasks(); }
        catch (Exception e) { return 0; }
    }

    private double gauge(String name, double def) {
        try { return registry.get(name).gauge().value(); } catch (Exception e) { return def; }
    }
}
