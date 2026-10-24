package com.threadpoollab.filter;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.util.ContentCachingResponseWrapper;
import java.io.IOException;

@Component
@Order(1)
public class TimingFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest req = (HttpServletRequest) request;
        HttpServletResponse res = (HttpServletResponse) response;

        // Wrap response so we can set headers AFTER chain.doFilter() without "already committed" issue
        ContentCachingResponseWrapper wrapped = new ContentCachingResponseWrapper(res);

        long threadStart = System.currentTimeMillis();
        String sentAt = req.getHeader("X-Sent-At");

        wrapped.setHeader("X-Thread-Name", Thread.currentThread().getName());
        wrapped.setHeader("X-Thread-Start", String.valueOf(threadStart));
        wrapped.setHeader("Access-Control-Allow-Origin", "*");
        wrapped.setHeader("Access-Control-Expose-Headers",
            "X-Thread-Name,X-Thread-Start,X-Wait-Ms,X-Exec-Ms,X-Complete-At");

        if (sentAt != null) {
            try {
                long wait = threadStart - Long.parseLong(sentAt);
                wrapped.setHeader("X-Wait-Ms", String.valueOf(Math.max(0, wait)));
            } catch (NumberFormatException ignored) {}
        }

        try {
            chain.doFilter(request, wrapped);
        } finally {
            long done = System.currentTimeMillis();
            // These headers are safe to set because ContentCachingResponseWrapper
            // buffers the body and hasn't written it to the underlying response yet
            wrapped.setHeader("X-Exec-Ms", String.valueOf(done - threadStart));
            wrapped.setHeader("X-Complete-At", String.valueOf(done));
            // Now write the buffered body to the real response
            wrapped.copyBodyToResponse();
        }
    }
}
