; Targets: tree-sitter-cpp via tree-sitter-language-pack >=0.13.0
; Capture convention: @def.name for definitions, @ref.name for references
; Note: struct forward declarations (no body) are excluded intentionally.

;; Definitions
(class_specifier
  name: (type_identifier) @def.name) @definition.class

(struct_specifier
  name: (type_identifier) @def.name
  body: (_)) @definition.class

(function_declarator
  declarator: (identifier) @def.name) @definition.function

(function_declarator
  declarator: (field_identifier) @def.name) @definition.function

(function_declarator
  declarator: (qualified_identifier
    name: (identifier) @def.name)) @definition.method

(enum_specifier
  name: (type_identifier) @def.name) @definition.type

(type_definition
  declarator: (type_identifier) @def.name) @definition.type

(namespace_definition
  name: (namespace_identifier) @def.name) @definition.namespace

;; References — includes
(preproc_include
  path: (string_literal) @ref.name) @reference.include

(preproc_include
  path: (system_lib_string) @ref.name) @reference.include

;; References — function calls
(call_expression
  function: (identifier) @ref.name) @reference.call

(call_expression
  function: (qualified_identifier
    name: (identifier) @ref.name)) @reference.call

(call_expression
  function: (field_expression
    field: (field_identifier) @ref.name)) @reference.call
