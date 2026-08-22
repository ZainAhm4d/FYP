/**
 * Form Validation Utilities
 * Enhanced validation with visual feedback
 */

const Validation = {
    /**
     * Validation rules
     */
    rules: {
        required: (value) => value !== null && value !== undefined && value.toString().trim() !== '',
        email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
        minLength: (value, length) => value.length >= length,
        maxLength: (value, length) => value.length <= length,
        numeric: (value) => !isNaN(value) && isFinite(value),
        alphanumeric: (value) => /^[a-zA-Z0-9]+$/.test(value),
        url: (value) => {
            try {
                new URL(value);
                return true;
            } catch {
                return false;
            }
        },
        match: (value, targetValue) => value === targetValue
    },

    /**
     * Validate a single field
     * @param {HTMLElement} field - Input element
     * @param {object} validations - Validation rules
     * @returns {object} Validation result {valid, message}
     */
    validateField(field, validations = {}) {
        const value = field.value;
        let valid = true;
        let message = '';

        // Required check
        if (validations.required && !this.rules.required(value)) {
            valid = false;
            message = validations.requiredMessage || 'This field is required';
        }

        // Email check
        if (valid && validations.email && value && !this.rules.email(value)) {
            valid = false;
            message = validations.emailMessage || 'Please enter a valid email address';
        }

        // Min length check
        if (valid && validations.minLength && value && !this.rules.minLength(value, validations.minLength)) {
            valid = false;
            message = validations.minLengthMessage || `Minimum ${validations.minLength} characters required`;
        }

        // Max length check
        if (valid && validations.maxLength && value && !this.rules.maxLength(value, validations.maxLength)) {
            valid = false;
            message = validations.maxLengthMessage || `Maximum ${validations.maxLength} characters allowed`;
        }

        // Numeric check
        if (valid && validations.numeric && value && !this.rules.numeric(value)) {
            valid = false;
            message = validations.numericMessage || 'Please enter a valid number';
        }

        // Custom validation function
        if (valid && validations.custom && typeof validations.custom === 'function') {
            const customResult = validations.custom(value);
            if (customResult !== true) {
                valid = false;
                message = typeof customResult === 'string' ? customResult : 'Invalid value';
            }
        }

        return { valid, message };
    },

    /**
     * Apply validation styling to field
     * @param {HTMLElement} field - Input element
     * @param {boolean} valid - Whether field is valid
     * @param {string} message - Feedback message
     */
    applyFieldStyling(field, valid, message) {
        // Remove existing validation classes
        field.classList.remove('is-valid', 'is-invalid');

        // Find or create feedback element
        let feedback = field.parentElement.querySelector('.form-feedback');
        
        if (!feedback && message) {
            feedback = document.createElement('div');
            feedback.className = 'form-feedback';
            field.parentElement.appendChild(feedback);
        }

        if (valid) {
            field.classList.add('is-valid');
            if (feedback) {
                feedback.classList.remove('invalid-feedback');
                feedback.classList.add('valid-feedback');
                feedback.innerHTML = `
                    <svg class="form-feedback-icon" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    ${message || 'Looks good!'}
                `;
            }
        } else {
            field.classList.add('is-invalid');
            if (feedback) {
                feedback.classList.remove('valid-feedback');
                feedback.classList.add('invalid-feedback');
                feedback.innerHTML = `
                    <svg class="form-feedback-icon" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    ${message}
                `;
            }
        }
    },

    /**
     * Clear validation styling from field
     * @param {HTMLElement} field - Input element
     */
    clearFieldStyling(field) {
        field.classList.remove('is-valid', 'is-invalid');
        const feedback = field.parentElement.querySelector('.form-feedback');
        if (feedback) {
            feedback.remove();
        }
    },

    /**
     * Validate form on submit
     * @param {HTMLFormElement} form - Form element
     * @param {object} fieldValidations - Validation rules for each field
     * @returns {boolean} Whether form is valid
     */
    validateForm(form, fieldValidations = {}) {
        let isValid = true;

        Object.keys(fieldValidations).forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (!field) return;

            const result = this.validateField(field, fieldValidations[fieldName]);
            this.applyFieldStyling(field, result.valid, result.message);

            if (!result.valid) {
                isValid = false;
                // Focus first invalid field
                if (isValid === false && !field.matches(':focus')) {
                    field.focus();
                }
            }
        });

        return isValid;
    },

    /**
     * Setup real-time validation for a form
     * @param {HTMLFormElement} form - Form element
     * @param {object} fieldValidations - Validation rules for each field
     */
    setupRealTimeValidation(form, fieldValidations = {}) {
        Object.keys(fieldValidations).forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (!field) return;

            // Validate on blur
            field.addEventListener('blur', () => {
                const result = this.validateField(field, fieldValidations[fieldName]);
                this.applyFieldStyling(field, result.valid, result.message);
            });

            // Clear validation on focus
            field.addEventListener('focus', () => {
                this.clearFieldStyling(field);
            });

            // Optional: Validate while typing (after field has been touched)
            let touched = false;
            field.addEventListener('input', () => {
                if (touched) {
                    const result = this.validateField(field, fieldValidations[fieldName]);
                    this.applyFieldStyling(field, result.valid, result.message);
                }
            });
            field.addEventListener('blur', () => {
                touched = true;
            }, { once: true });
        });
    },

    /**
     * Add character counter to textarea/input
     * @param {HTMLElement} field - Input/textarea element
     * @param {number} maxLength - Maximum character length
     */
    addCharCounter(field, maxLength) {
        const counter = document.createElement('div');
        counter.className = 'char-counter';
        counter.textContent = `0 / ${maxLength}`;
        field.parentElement.appendChild(counter);

        field.addEventListener('input', () => {
            const length = field.value.length;
            counter.textContent = `${length} / ${maxLength}`;

            // Update counter color based on proximity to limit
            counter.classList.remove('limit-near', 'limit-exceeded');
            if (length > maxLength) {
                counter.classList.add('limit-exceeded');
            } else if (length > maxLength * 0.9) {
                counter.classList.add('limit-near');
            }
        });
    },

    /**
     * Show custom error on field
     * @param {HTMLElement} field - Input element
     * @param {string} message - Error message
     */
    showError(field, message) {
        this.applyFieldStyling(field, false, message);
    },

    /**
     * Show custom success on field
     * @param {HTMLElement} field - Input element
     * @param {string} message - Success message
     */
    showSuccess(field, message = 'Looks good!') {
        this.applyFieldStyling(field, true, message);
    },

    /**
     * Clear all validation from form
     * @param {HTMLFormElement} form - Form element
     */
    clearForm(form) {
        const fields = form.querySelectorAll('.form-input, .form-select, .form-textarea');
        fields.forEach(field => {
            this.clearFieldStyling(field);
        });
    }
};

// Make globally available
window.Validation = Validation;
