package com.engonow.lms.mapper;

import com.engonow.lms.dto.SlotResponseDTO;
import com.engonow.lms.entity.TutorAvailabilitySlot;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.IGNORE)
public interface SlotMapper {

    @Mapping(source = "tutor.id", target = "tutorId")
    @Mapping(source = "tutor.fullName", target = "tutorName")
    @Mapping(source = "slotStatus", target = "slotStatus")
    SlotResponseDTO toDTO(TutorAvailabilitySlot slot);
}
