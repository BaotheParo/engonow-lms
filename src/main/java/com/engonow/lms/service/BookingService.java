package com.engonow.lms.service;

import com.engonow.lms.dto.BookingRequestDTO;
import com.engonow.lms.entity.MockTestBooking;

public interface BookingService {
    MockTestBooking createBooking(BookingRequestDTO requestDTO);
}
