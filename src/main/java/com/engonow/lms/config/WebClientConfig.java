package com.engonow.lms.config;

import io.netty.channel.ChannelOption;
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * WebClient bean for outbound HTTP calls to the Python OMR Microservice.
 *
 * Configured with explicit timeouts to prevent the calling thread from
 * hanging indefinitely if the Python service is unresponsive:
 *  - connectTimeout: max time to establish TCP connection.
 *  - readTimeout: max time waiting for response bytes after connection.
 *  - responseTimeout: end-to-end timeout for the full request-response cycle.
 */
@Configuration
public class WebClientConfig {

    @Value("${app.omr-service.base-url}")
    private String omrServiceBaseUrl;

    @Bean(name = "omrWebClient")
    public WebClient omrWebClient() {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
            .responseTimeout(Duration.ofSeconds(30))
            .doOnConnected(conn -> conn
                .addHandlerLast(new ReadTimeoutHandler(30, TimeUnit.SECONDS))
                .addHandlerLast(new WriteTimeoutHandler(10, TimeUnit.SECONDS))
            );

        return WebClient.builder()
            .baseUrl(omrServiceBaseUrl)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .defaultHeader("Content-Type", "application/json")
            .defaultHeader("X-Client-Id", "engonow-lms")
            .build();
    }
}
