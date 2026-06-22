package com.engonow.lms.repository;

import com.engonow.lms.entity.Exam;
import com.engonow.lms.enums.ExamType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ExamRepository extends JpaRepository<Exam, Long> {

    List<Exam> findByIsActiveTrueOrderByCreatedAtDesc();

    List<Exam> findByExamTypeAndIsActiveTrue(ExamType examType);

    /**
     * JOIN FETCH answerKeys to load exam + all answer keys in ONE SQL query.
     * This is the canonical way to avoid the N+1 problem when the grading
     * service needs both the exam metadata and the answer keys together.
     *
     * WARNING: Do NOT use this for paginated list endpoints — JOIN FETCH
     * with pagination causes Hibernate's in-memory pagination warning.
     * Use it only for single-entity detail/grading fetches.
     */
    @Query("""
           SELECT e FROM Exam e
           JOIN FETCH e.answerKeys ak
           WHERE e.id = :examId
             AND e.isActive = true
           ORDER BY ak.questionNumber ASC
           """)
    Optional<Exam> findByIdWithAnswerKeys(@Param("examId") Long examId);
}
