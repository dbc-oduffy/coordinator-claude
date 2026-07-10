; Targets: tree-sitter-tsx via tree-sitter-language-pack >=0.13.0
; TSX is a superset of TypeScript — same query patterns apply.
; Capture convention: @def.name for definitions, @ref.name for references

;; Definitions
(function_declaration
  name: (identifier) @def.name) @definition.function

(class_declaration
  name: (type_identifier) @def.name) @definition.class

(interface_declaration
  name: (type_identifier) @def.name) @definition.interface

(type_alias_declaration
  name: (type_identifier) @def.name) @definition.type

(enum_declaration
  name: (identifier) @def.name) @definition.enum

(method_definition
  name: (property_identifier) @def.name) @definition.method

;; References — type annotations
(type_annotation
  (type_identifier) @ref.name) @reference.type

;; References — new expressions
(new_expression
  constructor: (identifier) @ref.name) @reference.class

;; References — function calls
(call_expression
  function: (identifier) @ref.name) @reference.call

(call_expression
  function: (member_expression
    property: (property_identifier) @ref.name)) @reference.call

;; Definitions — const/let/var declarations (React components, hooks, constants)
(lexical_declaration
  (variable_declarator
    name: (identifier) @def.name)) @definition.variable
