package com.threadpoollab.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
import java.util.LinkedHashMap;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")
public class WorkloadController {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @GetMapping("/fast")
    public Map<String,Object> fast() {
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","fast"); m.put("thread",Thread.currentThread().getName()); m.put("ts",System.currentTimeMillis());
        return m;
    }

    @GetMapping("/io")
    public Map<String,Object> io(@RequestParam(defaultValue="200") long ms) throws InterruptedException {
        long s = System.currentTimeMillis();
        Thread.sleep(ms);
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","io"); m.put("thread",Thread.currentThread().getName());
        m.put("slept",ms); m.put("elapsed",System.currentTimeMillis()-s);
        return m;
    }

    @GetMapping("/cpu")
    public Map<String,Object> cpu(@RequestParam(defaultValue="100000000") long iterations) {
        long s = System.currentTimeMillis(); long result = 0;
        for (long i=0;i<iterations;i++) result += (long)(Math.sqrt(i)*Math.sin(i));
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","cpu"); m.put("thread",Thread.currentThread().getName());
        m.put("result",result%1000); m.put("elapsed",System.currentTimeMillis()-s);
        return m;
    }

    @GetMapping("/db")
    public Map<String,Object> db(@RequestParam(defaultValue="100") int rows) {
        long s = System.currentTimeMillis();
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM (SELECT 1 FROM information_schema.COLUMNS LIMIT ?) t",Integer.class,rows);
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","db"); m.put("thread",Thread.currentThread().getName());
        m.put("rows",count!=null?count:0); m.put("elapsed",System.currentTimeMillis()-s);
        return m;
    }

    @GetMapping("/db-sleep")
    public Map<String,Object> dbSleep(@RequestParam(defaultValue="200") long ms) {
        long s = System.currentTimeMillis();
        jdbcTemplate.execute("SELECT SLEEP("+(ms/1000.0)+")");
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","db-sleep"); m.put("thread",Thread.currentThread().getName());
        m.put("elapsed",System.currentTimeMillis()-s);
        return m;
    }

    @GetMapping("/slow")
    public Map<String,Object> slow(@RequestParam(defaultValue="3000") long ms) throws InterruptedException {
        Thread.sleep(ms);
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("type","slow"); m.put("thread",Thread.currentThread().getName()); m.put("slept",ms);
        return m;
    }

    @GetMapping("/warmup")
    public Map<String,Object> warmup() throws InterruptedException {
        Thread.sleep(50);
        return Map.of("status","warmed","thread",Thread.currentThread().getName());
    }
}
