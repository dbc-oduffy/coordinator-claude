; Targets: tree-sitter-javascript via tree-sitter-language-pack >=0.13.0
; JavaScript — no type annotations, interfaces, enums, or type aliases.
; Capture convention: @def.name for definitions, @ref.name for references

;; Definitions
(function_declaration
  name: (identifier) @def.name) @definition.function

(class_declaration
  name: (identifier) @def.name) @definition.class

(method_definition
  name: (property_identifier) @def.name) @definition.method

;; Definitions — const/let/var declarations (React components, hooks, constants)
(lexical_declaration
  (variable_declarator
    name: (identifier) @def.name)) @definition.variable

;; References — new expressions
(new_expression
  constructor: (identifier) @ref.name) @reference.class

;; References — function calls
(call_expression
  function: (identifier) @ref.name) @reference.call

(call_expression
  function: (member_expression
    property: (property_identifier) @ref.name)) @reference.call
