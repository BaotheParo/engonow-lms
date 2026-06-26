package com.engonow.lms.dto;

import com.engonow.lms.enums.AnswerOption;
import com.fasterxml.jackson.annotation.JsonProperty;

public record OmrAnswer(
    @JsonProperty("question_number") Integer questionNumber,
    @JsonProperty("student_answer") AnswerOption studentAnswer
) {}
