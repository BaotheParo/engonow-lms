package com.engonow.lms.mapper;

import com.engonow.lms.dto.SubmissionResponseDTO;
import com.engonow.lms.entity.TestSubmission;
import com.engonow.lms.entity.SubmissionDetail;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.Named;
import org.mapstruct.ReportingPolicy;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.IGNORE)
public interface SubmissionMapper {

    @Mapping(source = "id", target = "submissionId")
    @Mapping(source = "exam.id", target = "examId")
    @Mapping(source = "student.id", target = "studentId")
    @Mapping(source = "score", target = "totalCorrect")
    @Mapping(source = "percentage", target = "percentage", qualifiedByName = "doubleToBigDecimal")
    @Mapping(source = "details", target = "questionResults")
    SubmissionResponseDTO toResponseDto(TestSubmission submission);

    @Mapping(source = "questionNumber", target = "questionNumber")
    @Mapping(source = "studentAnswer", target = "studentAnswer")
    @Mapping(source = "correctAnswer", target = "correctAnswer")
    @Mapping(source = "isCorrect", target = "isCorrect")
    SubmissionResponseDTO.QuestionResult toQuestionResultDto(SubmissionDetail detail);

    @Named("doubleToBigDecimal")
    default BigDecimal doubleToBigDecimal(Double value) {
        if (value == null) return null;
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
    }
}
